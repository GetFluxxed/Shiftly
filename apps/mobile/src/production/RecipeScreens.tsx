import React, { useCallback } from 'react';
import { StyleSheet } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { Body, Button, Card, EmptyState, Heading, Loading, Notice, Pill } from '@/src/ui/components';
import { Text } from '@/src/ui/Typography';
import { colors } from '@/src/ui/theme';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { InventorySearch, LoadError, Pages, useInventoryResource } from '@/src/inventory/shared';
import { InventoryItem, InventoryList } from '@/src/inventory/InventoryItem';
import { validProductionId, type Recipe } from './api';
import { ProductionPage, useProduction } from './shared';
import { RecipeEditorModal } from './RecipeEditorModal';
import { useAppNavigation } from '@/src/navigation/useAppNavigation';

export function RecipesScreen() {
  return <ProductionPage title="Recipe"><RecipeBook /></ProductionPage>;
}
function RecipeBook() {
  const { api, canManageRecipes } = useProduction(); const navigation = useAppNavigation();
  const [filters, setFilters] = useRememberedState('production.recipes.list', { query: '', search: '', cursor: '' });
  const resource = useInventoryResource(useCallback(() => api.recipes(filters.search, filters.cursor), [api, filters.search, filters.cursor]));
  return <><Card><Heading>Recipes</Heading><Body>Batch yields and ingredients.</Body>
    {canManageRecipes ? <Button title="New recipe" icon="add" onPress={() => navigation.open('/production/recipes/new')} /> : null}
    <InventorySearch label="Find a recipe" value={filters.query} onChange={query => setFilters(v => ({ ...v, query }))} submitLabel="Find recipes" onSubmit={() => setFilters(v => ({ ...v, search: v.query.trim(), cursor: '' }))} />
  </Card>{resource.loading ? <Loading label="Opening the recipe book…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <>
    {!resource.data.items.length ? <Card><EmptyState icon="restaurant-outline" title="No recipes here yet" description={canManageRecipes ? 'Create the first recipe when you are ready.' : 'A manager or owner can add recipes for this store.'} /></Card> : null}
    <InventoryList>{resource.data.items.map(item => {
      const ingredientCount = item.ingredients.length + (item.referenceIngredients?.length ?? 0);
      return <InventoryItem key={item.id} title={item.name} subtitle={`Makes ${item.yieldAmount} ${item.yieldUnit}`} detail={`${ingredientCount} ingredient${ingredientCount === 1 ? '' : 's'}`} onPress={() => navigation.open({ pathname: '/production/recipes/[recipeId]', params: { recipeId: item.id } })} />;
    })}</InventoryList>
    <Pages next={resource.data.nextCursor} cursor={filters.cursor} setCursor={cursor => setFilters(v => ({ ...v, cursor }))} />
  </>}</>;
}

export function NewRecipeScreen() {
  const navigation = useAppNavigation();
  return <ProductionPage title="Recipe" backTo="/production/recipes"><RecipeBook /><RecipeEditorModal visible onClose={() => navigation.back('/production/recipes')} onSaved={saved => navigation.replace({ pathname: '/production/recipes/[recipeId]', params: { recipeId: saved.id } })} /></ProductionPage>;
}
export function RecipeScreen() {
  const { recipeId } = useLocalSearchParams<{ recipeId: string }>();
  return <ProductionPage title="Recipe" backTo="/production/recipes">{validProductionId(recipeId) ? <RecipeLoader id={recipeId} /> : <Notice message="This recipe is unavailable." kind="error" />}</ProductionPage>;
}
function RecipeLoader({ id }: { id: string }) {
  const { api, canManageRecipes } = useProduction(); const navigation = useAppNavigation(); const resource = useInventoryResource(useCallback(() => api.recipe(id), [api, id]));
  const [editing, setEditing, resetEditing] = useRememberedState(`production.recipe.${id}.editing`, false, resource.data ? `${resource.data.version}:${resource.data.revisionId}` : id);
  if (resource.loading) return <Loading label="Opening recipe…" />;
  if (resource.error || !resource.data) return <LoadError {...resource} />;
  const item = resource.data;
  return <><Card><Heading>Recipe</Heading><Text style={styles.recipeTitle}>{item.name}</Text><Pill label={`Makes ${item.yieldAmount} ${item.yieldUnit}`} />{item.instructions ? <Body>{item.instructions}</Body> : null}
    {canManageRecipes ? <><Button title="Edit recipe" variant="secondary" onPress={() => setEditing(true)} /><Button title="New recipe" icon="add" onPress={() => navigation.open('/production/recipes/new')} /></> : null}</Card><IngredientSummary item={item} />
    <RecipeEditorModal item={item} visible={editing} onClose={resetEditing} onSaved={() => { resetEditing(); void resource.refresh(); }} /></>;
}
function IngredientSummary({ item }: { item: Recipe }) {
  const renderSection = (section: 'base' | 'variegato', heading: string) => {
    const tracked = item.ingredients.filter(ingredient => (ingredient.section ?? 'base') === section);
    const references = (item.referenceIngredients ?? []).filter(ingredient => (ingredient.section ?? 'base') === section);
    if (!tracked.length && !references.length) return null;
    return <><Heading>{heading}</Heading><InventoryList>{tracked.map(ingredient => {
      const changed = ingredient.currentBaseUnit && ingredient.currentBaseUnit !== ingredient.baseUnit;
      return <InventoryItem key={`${section}:${ingredient.productId}`} title={ingredient.name}
        subtitle={changed ? `Stock unit changed to ${ingredient.currentBaseUnit}` : undefined} detail={`${ingredient.amount} ${ingredient.unit}`} />;
    })}{references.map((ingredient, index) => <InventoryItem key={`${section}:reference:${index}:${ingredient.name}`}
      title={ingredient.name} subtitle="Recipe only" detail={`${ingredient.amount} ${ingredient.unit}`} />)}</InventoryList></>;
  };
  return <>{renderSection('base', 'Ingredients')}{renderSection('variegato', 'Variegato')}</>;
}
const styles = StyleSheet.create({ recipeTitle: { color: colors.ink, fontSize: 30, lineHeight: 36, fontWeight: '700' } });
